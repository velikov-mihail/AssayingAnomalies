function [out]=scattermap(long,lat,var1,var2,opt,varargin)
% PURPOSE: This function links a map and a two-dimensionnal scatterplot
%------------------------------------------------------------------------
% USAGE: out=scattermap(long,lat,var1,var2,opt,quantiles,qvar,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           var1 = n x 1 vector of the variable to study on the first axis
%           var2 = n x 1 vector of the variable to study on the second axis
%           opt = parameter that tells how to draw the scatterplot
%                   * opt=1 : the scatterplot alone is drawn
%                   * opt=2 : a kernel mean estimator is added
%                   * opt=3 : quantiles are added ( see following optional parameter )
%           quantiles = optionnal vector of quantile orders to draw
%           qvar = qualitative variable
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on either the map or the scatterplot by clicking with the left mouse button
%         You can select points inside a polygon: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         You can select points that have the same qvar value by pushing buttons 0-9 on the keybord.
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses quant.m, fastbinsmooth.m, setdens.m, selectmap.m, selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
c=0;
l=0;
symbol=0;
affc=-1;
class=0; %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

vectx=[];
vecty=[];
name1=inputname(3);
name2=inputname(4);

if opt==2 | opt==3
    global v1glob;
    global v2glob;
    if opt==3
        global quantiles;
        global quanti;
    end;
    v1glob=var1;
    v2glob=var2;
    
end;



%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save scatfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%



% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        quantiles=varargin{1};
    end;
    
    if t>=2 & ~isempty(varargin{2})
        qvar=varargin{2};                   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        class=1;
        qname=inputname(7);
    end;
    
    if t>=3 & ~isempty(varargin{3})
        carte=varargin{3};
        c=1;
    end;
    if t>=4 & ~isempty(varargin{4})
        label=varargin{4};
        l=1;
    end;
    if t==5 & ~isempty(varargin{5})
        symbol=varargin{5};
    end;
end;

%%%%%%%%%%%%%%%%%%%%%


if class==1
    qvarsort=sort(qvar);
    N=histc(qvar,qvarsort');
    qvalues=qvarsort(find(N~=0));
    nbc=length(qvalues);
    affc=zeros(nbc,1);
    vectclass=cell(1,nbc);
    Hbutt=zeros(nbc,1);
    col{1}=[220/255,210/255,183/255];
    col{2}=[207/255,203/255,18/255];
    col{3}=[240/255,134/255,214/255];
    col{4}=[254/255,194/255,203/255];
    col{5}=[150/255,118/255,133/255];
    col{6}=[132/255,221/255,160/255];
    col{7}=[92/255,133/255,94/255];
    col{8}=[233/255,168/255,97/255];
    col{9}=[121/255,50/255,6/255];
    col{10}=[158/255,216/255,235/255];
    for i=1:nbc
        vectclass{i}=find(qvar==qvalues(i));
        Hbutt(i)=uicontrol('Style','togglebutton','string',[qname,'=',num2str(qvalues(i))],'BackGroundColor',col{i},'Units','Normalized','Position',[0.14+(i-1)*0.06,0.025,0.047,0.026],'Enable','inactive');
    end;   
  
end;


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

% Trace the scatter plot

Axis2=subplot(1,2,2);
plot(var1,var2,'b.');
title('Scatter Plot');
xlabel(name1);
ylabel(name2);
axis manual;
subplot(Axis1);
axis manual;

Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%
% Compute the quantiles if necessary
if opt==3
    global Hslide;
    global Ht;
    alpha=20;
    evalv1=[min(var1):(max(var1)-min(var1))/100:max(var1)]';
    Hslide=uicontrol('Style','slider','Min',0,'Max',100,'Value',20);
    set(Hslide,'Units','normalized');
    set(Hslide,'Position',[0.015,0.025,0.047,0.026]);
    Ht=uicontrol('Style','text','String',[num2str(get(Hslide,'Value')),'%'],'Position',[100,20,60,20],'Enable','inactive');
    set(Ht,'Units','normalized');
    set(Ht,'Position',[0.078,0.025,0.047,0.026]);
    for i=1:length(quantiles)
        quanti(:,i)=quant(var1,var2,quantiles(i),alpha);
    end;
    set(Hslide,'Callback','setdensq'); % Call to setdensq.m when the slider is clicked
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Create the slider if necessary
if opt==2    
    global Hslide;
    global Ht;
    global eval;
    global r;
    h=0.4*(max(var1)-min(var1))/2;
    Hslide=uicontrol('Style','slider','Min',0,'Max',100,'Value',40);
    set(Hslide,'Units','normalized');
    set(Hslide,'Position',[0.015,0.025,0.047,0.026]);
    Ht=uicontrol('Style','text','String',[num2str(get(Hslide,'Value')),'%'],'Position',[100,20,60,20],'Enable','inactive');
    set(Ht,'Units','normalized');
    set(Ht,'Position',[0.078,0.025,0.047,0.026]);
    eval=[min(var1):(max(var1)-min(var1))/200:max(var1)]';
    
    r=fastbinsmooth([var1';var2'],h,[min(var1),max(var1)],201,2,3,0,1);
    set(Hslide,'Callback','setdens'); % Call to setdens.m when the slider is clicked
end;
%%%%%%%%%%%%%%%%%%%%

% Main loop
maptest=0;
scattertest=0;
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
    if ~isempty(Iunselect)
      plot(var1(Iunselect),var2(Iunselect),'b.');
    end;
    if opt==2
         plot(eval',r,'k');
    end;
    if opt==3
        for i=1:length(quantiles)
            plot(evalv1,quanti(:,i),'y');
        end;
    end;
    
    
    if class==1
        for i=1:nbc
            if affc(i)==1
                plot(var1(vectclass{i}),var2(vectclass{i}),'.','color',col{i}); %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
            end;        
        end;
    end;
    
    
    if ~isempty(Iselect) & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52 & BUTTON~=53 & BUTTON~=54 & BUTTON~=55 & BUTTON~=56 & BUTTON~=57 & BUTTON~=48
        if maptest==1
            if symbol==1
                plot(var1(Iselect),var2(Iselect),'r*');
            else
                plot(var1(Iselect),var2(Iselect),'r.');
            end;
        elseif scattertest==1
            if symbol==1
                plot(var1(Iselect),var2(Iselect),'mo');
            else
                plot(var1(Iselect),var2(Iselect),'m.'); 
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
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
    
    if class==1
        for i=1:nbc
            if affc(i)==1
                plot(long(vectclass{i}),lat(vectclass{i}),'.','color',col{i}); %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
                if l==1
                    Htex=text(long(vectclass{i}),lat(vectclass{i}),num2str(label(vectclass{i})));
                    set(Htex,'FontSize',8);
                end;
            end;        
        end;
    end;
    
    
    if ~isempty(Iselect) & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52 & BUTTON~=53 & BUTTON~=54 & BUTTON~=55 & BUTTON~=56 & BUTTON~=57 & BUTTON~=48
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'r*');
            else
                plot(long(Iselect),lat(Iselect),'r.');
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif scattertest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'mo');
            else
                plot(long(Iselect),lat(Iselect),'m.');              
            end;
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    
    
    if class==1
        if (BUTTON==49 | BUTTON==50 | BUTTON==51 | BUTTON==52 | BUTTON==53 | BUTTON==54 | BUTTON==55 | BUTTON==56 | BUTTON==57 | BUTTON==48) & isempty(find(affc~=0))
            obs=zeros(size(long,1),1);
            maptest=0;
            scattertest=0;
        end;
    end;
    % class selection
    if (BUTTON==49 | BUTTON==50 | BUTTON==51 | BUTTON==52 | BUTTON==53 | BUTTON==54 | BUTTON==55 | BUTTON==56 | BUTTON==57 | BUTTON==48)
        maptest=0;
        scattertest=0;
        [obs,affc]=selectstat('scatter',obs,var1,'class',var2,BUTTON,Hbutt,vectclass,affc);
    end;
    
    
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0      
            maptest=1;
            scattertest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52 & BUTTON~=53 & BUTTON~=54 & BUTTON~=55 & BUTTON~=56 & BUTTON~=57 & BUTTON~=48
            if ~isempty(find(affc==1))
                obs=zeros(size(long,1),1);
                for i=1:nbc
                    set(Hbutt(i),'Value',0);
                end;
                affc=zeros(nbc,1);
            end;
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            if ~isempty(find(affc==1))
                obs=zeros(size(long,1),1);
                for i=1:nbc
                    set(Hbutt(i),'Value',0);
                end;
                affc=zeros(nbc,1);
            end;
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % scatterplot selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if scattertest==0
            scattertest=1;
            maptest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52 & BUTTON~=53 & BUTTON~=54 & BUTTON~=55 & BUTTON~=56 & BUTTON~=57 & BUTTON~=48
            if ~isempty(find(affc==1))
                obs=zeros(size(long,1),1);
                for i=1:nbc
                    set(Hbutt(i),'Value',0);
                end;
                affc=zeros(nbc,1);
            end;
            obs=selectstat('scatter',obs,var1,'point',var2,x,y);
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            if ~isempty(find(affc==1))
                obs=zeros(size(long,1),1);
                for i=1:nbc
                    set(Hbutt(i),'Value',0);
                end;
                affc=zeros(nbc,1);
            end;
            [obs,vectx,vecty]=selectstat('scatter',obs,var1,'poly',var2,x,y);
        end;
        %%%%%%%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out=obs;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%