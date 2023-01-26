function [out]=variocloudmap(long,lat,variable,robust,opt,varargin)
% PURPOSE: This function links a map and a variogram cloud (only the variogram cloud is active)
%------------------------------------------------------------------------
% USAGE: out=variocloudmap(long,lat,variable,robust,opt,quantiles,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           variable = n x 1 vector of the variable to study
%           robust = parameter that tells how to calculate the variogram
%                   * robust=0: usual version
%                   * robust=1: robust version
%           opt = parameter that tells how to draw the scatterplot
%                   * opt=1 : the scatterplot alone is drawn
%                   * opt=2 : a kernel mean estimator is added
%                   * opt=3 : quantiles are added ( see following optionnal parameter )
%           quantiles = optionnal vector of quantile orders to draw
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% NOTES: This fonction uses the function fastbinsmooth.m to calculate the mean estimator
%------------------------------------------------------------------------
% MANUAL: Select points on the variogram cloud by clicking with the left mouse button
%         You can select points inside a polygon: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         Selection is lost when you click on the map
%         To quit, click the middle button or press 'q'
%------------------------------------------------------------------------
% uses setdens.m, fastbinsmooth.m, quant.m, selectmap.m, selectstat.m
%------------------------------------------------------------------------
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-



close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
c=0;
l=0;
symbol=0;
vectx=[];
vecty=[];
name=inputname(3);
L=sparse(length(lat),length(lat)); % linkage matrix
Tp1=repmat(lat',length(lat),1);
Tp2=repmat(long',length(long),1);
H=sqrt((repmat(lat,1,length(lat))-Tp1).^2+(repmat(long,1,length(long))-Tp2).^2);

if robust==0
    V=(repmat(variable,1,length(lat))-repmat(variable',length(lat),1)).^2;
    V=0.5*V;
elseif robust==1
    V=sqrt(abs(repmat(variable,1,length(lat))-repmat(variable',length(lat),1)));
    V=0.5*V;
end;

mask=sparse(triu(ones(length(lat),length(lat))));
Htri=H(find(mask==1));
Vtri=V(find(mask==1));


%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save variofich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%



% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        quantiles=varargin{1};
    end;
    if  t>=2 & ~isempty(varargin{2})
        carte=varargin{2};
        c=1;
    end;
    if  t>=3 & ~isempty(varargin{3})
        label=varargin{3};
        l=1;
    end;   
    if t==4 & ~isempty(varargin{4})
        symbol=varargin{4};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%%%%%%%%


% Trace the variogram cloud
Axis2=subplot(1,2,2);
plot(H,V,'b.');
title(['variogram cloud: ',name]);
xlabel('distance');
axis manual;
subplot(Axis1);
axis manual;

Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%


% Create the slider if necessary
if opt==2
    global Hslide;
    global Ht;
    global v1glob;
    global eval;
    global v2glob;
    global eval;
    global r;
    v1glob=Htri;
    v2glob=Vtri;
    h=0.4*(max(H(:))-min(H(:)))/2;
    Hslide=uicontrol('Style','slider','Min',0,'Max',100,'Value',40);
    Ht=uicontrol('Style','text','String',[num2str(get(Hslide,'Value')),'%'],'Position',[100,20,60,20],'Enable','inactive');
    eval=[min(H(:)):(max(H(:))-min(H(:)))/200:max(H(:))]';
    set(Hslide,'Callback','setdens');
    r=fastbinsmooth([Htri';Vtri'],h,[min(H(:)),max(H(:))],201,2,3,0,1);
    
end;
%%%%%%%%%%%%%%%%%%%%
% Compute the quantiles if necessary
if opt==3
    evalv1=[min(Htri):(max(Htri)-min(Htri))/100:max(Htri)]';
    for i=1:length(quantiles)
        quanti(:,i)=quant(Htri,Vtri,quantiles(i),20);
    end;
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Main loop

BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    [LIselect,LJselect]=find(triu(L)==1);
    Lselect=find(triu(L)==1);
    Lunselect=find(L==0);
    if ~isempty(Lunselect)
        plot(H(Lunselect),V(Lunselect),'b.');
    end;
    if opt==2
         plot(eval',r,'k');
    end;
    if opt==3
        for i=1:length(quantiles)
            plot(evalv1,quanti(:,i),'k');
        end;
    end;
    if ~isempty(Iselect)
        if symbol==1
            plot(H(Lselect),V(Lselect),'mo');
        else
            plot(H(Lselect),V(Lselect),'m.');
        end;
        if ~isempty(vectx)
            plot(vectx,vecty,'k');
        end;
    end;
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if symbol==1
            plot(long(Iselect),lat(Iselect),'mo');
        else
            plot(long(Iselect),lat(Iselect),'m.');
        end;
        [LIselect,LJselect]=find(triu(L)==1);
        ligne=line([long(LIselect)' ;long(LJselect)'],[lat(LIselect)'; lat(LJselect)']);
        set(ligne,'Color','black');
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;  
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        obs=zeros(size(long,1),1);  
        L=sparse(length(lat),length(lat));
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % variocloud selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
%         if scattertest==0
%             scattertest=1;
%             maptest=0;
%             obs=zeros(size(long,1),1);
%         end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 
            [obs,L]=selectstat('vario',obs,variable,'point',H,V,Htri,Vtri,L,x,y);
        %%%%%%%%%%%%%%%%%%
        % polygon selection
    elseif BUTTON==3 
            [obs,L,vectx,vecty]=selectstat('vario',obs,variable,'poly',H,V,Htri,Vtri,L,x,y);
        end;
        %%%%%%%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out=obs;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%