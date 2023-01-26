function [out]=neighbormap(long,lat,variable,W,varargin)
% PURPOSE: This function links a map and a neighbour plot (scatterplot of variable against variable
% for the neighboring sites)
%------------------------------------------------------------------------
% USAGE: out=neighbormap(long,lat,variable,W,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           variable = n x 1 vector of the variable to study
%           W = weight matrix
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on the neighbour plot by clicking with the left mouse button
%         Select a point and his neighbour on the map by clicking with the left mouse button
%         You can select points inside a polygon and their neighbours: - right click to set the first point of the polygon
%                                                                      - left click to set the other points
%                                                                      - right click to close the polygon
%         Selection is lost when you click on the map
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses selectstat.m
%------------------------------------------------------------------------
% -----------------------------------------------------------------------
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
vectx=[];
vecty=[];
inter=[];
name=inputname(3);
L=sparse(length(lat),length(lat)); % linkage matrix
L2=sparse(length(lat),length(lat)); % display matrix
Iclick=zeros(length(variable),1);
%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save neighbfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%

% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        carte=varargin{1};
        c=1;
    end;
    if  t>=2 & ~isempty(varargin{2})
        label=varargin{2};
        l=1;
    end;
    if t==3 & ~isempty(varargin{3})
        symbol=varargin{3};
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

% Trace the neighbour plot

Axis2=subplot(1,2,2);
[I,J]=find(W~=0);
varn1=variable(I);
varn2=variable(J);
plot(varn1,varn2,'b.');
title('Neighbour Plot');
xlabel(name);
ylabel(name);
axis equal;
axis manual;
subplot(Axis1);
axis manual;

Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Main loop
BUTTON=0;
maptest=0;
neightest=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    plot(varn1,varn2,'b.');
    plot(varn1,varn1,'k-');
    axis equal;
    axis manual;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    [LIselect,LJselect]=find(L==1);
    [LIselect2,LJselect2]=find(L2==1);
    Iselclick=find(Iclick~=0);
    if ~isempty(Iselect)
        if neightest==1
            if symbol==1
                plot(variable(LIselect2),variable(LJselect2),'mo');
            else
                plot(variable(LIselect2),variable(LJselect2),'m.');
            end;
        elseif maptest==1
            if ~isempty(Iselclick)
                Jselclick=cell(1,length(Iselclick));
               
                for k=1:length(Iselclick)
                    Jselclick{k}=find(W(Iselclick(k),:)~=0);
                    if ~isempty(Jselclick{k})   
                        if symbol==1
                            plot(variable(Iselclick(k)),variable(Jselclick{k}),'r*');
                        else
                            plot(variable(Iselclick(k)),variable(Jselclick{k}),'r.');
                        end;
                    end;
                end;
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
    if ~isempty(Iselect)
        if neightest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'mo');
            else
                plot(long(Iselect),lat(Iselect),'m.');
            end;
        elseif maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'r*');
            else
                plot(long(Iselect),lat(Iselect),'r.');
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
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
        if maptest==0      
            maptest=1;
            neightest=0;
            obs=zeros(size(long,1),1);
            L=sparse(length(lat),length(lat));
            L2=sparse(length(lat),length(lat)); % display matrix
            Iclick=zeros(length(variable),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 
            [obs,L,Iclick]=selectstat('neighbour',obs,variable,'mappoint',I,J,W,L,x,y,long,lat,Iclick);   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,L,Iclick,vectx,vecty]=selectstat('neighbour',obs,variable,'mappoly',I,J,W,L,x,y,long,lat,Iclick);
        end;
    % neighbour plot selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        % point selection
        if neightest==0      
            maptest=0;
            neightest=1;
            obs=zeros(size(long,1),1);
            L=sparse(length(lat),length(lat));
            L2=sparse(length(lat),length(lat)); % display matrix
            Iclick=zeros(length(variable),1);
            vectx=[];
        end;
        if BUTTON~=3 & BUTTON~=2 
            [obs,L,L2]=selectstat('neighbour',obs,variable,'neigh',I,J,W,L,L2,x,y);
        %%%%%%%%%%%%%%%%%%
%         % polygon selection
%         elseif BUTTON==3 
%             vectx=x;
%             vecty=y;
%             BUTTON2=0;
%             p=0;
%             while BUTTON2~=3
%                 [xp,yp,BUTTON2]=ginput(1);
%                 if BUTTON2~=3
%                     vectx=[vectx;xp];
%                     vecty=[vecty;yp];
%                 elseif BUTTON2==3 & p~=0            
%                     vectx=[vectx;vectx(1)];
%                     vecty=[vecty;vecty(1)];
%                     obs2=inpolygon(var1,var2,vectx,vecty);
%                     Iunselect=find(and(obs,obs2)~=0); % index of already selected points inside the polygon 
%                     Iselect=find(xor(obs,obs2)~=0); % index of newly selected points
%                     obs(Iselect)=1;
%                     obs(Iunselect)=0;
%                 end;
%                 p=p+1;
%             end;
        end;
    end;
    %%%%%%%%%%%%%%%%%%
end;
out=obs;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%