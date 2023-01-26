function [out]=densitymap(lat,long,variable,alpha,varargin)
% PURPOSE: This function links a map and a density estimator
%------------------------------------------------------------------------
% USAGE: out=densitymap(lat,long,variable,alpha,carte,label,symbol)
%   where : lat = n x 1 vector of coordinates on the second axis
%           long = n x 1 vector of coordinates on the first axis
%           variable = n x 1 vector of the variable to study
%           alpha = used to calculate the band. band=(alpha/100)*(max(variable)-min(variable))/2
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% Notes: This fontion uses the function kern_den to calculate the density
%------------------------------------------------------------------------
% MANUAL: Select points on the map by clicking with the left mouse button
%         Select intervals on a density graph by clicking with the left mouse button
%         You can select points inside a polygon on the map: - right click to set the first point of the polygon
%                                                            - left click to set the other points
%                                                            - right click to close the polygon
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses setdens2.m, kern_de1.m, selectmap.m, selectstat.m
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
vectx=[];
vecty=[];
inter=[];
name=inputname(3);
global vglobal;
vglobal=variable;
    
%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save densfich  out -ascii' ...
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


% Create the slider
warning off;
global h;
warning on;
global Hslide;
global Ht;
global newx;
global dens;

Hslide=uicontrol('Style','slider','Min',0,'Max',100,'Value',alpha);
Ht=uicontrol('Style','text','String',[num2str(get(Hslide,'Value')),'%'],'Position',[100,20,60,20],'Enable','inactive');
set(Hslide,'Callback','setdens2'); % Call to setdens2.m when the slider is clicked
%%%%%%%%%%%%%%%%%%%%
% Trace the density
newx=linspace(min(variable),max(variable)+0.5,100);
h=(alpha/100)*(max(variable)-min(variable))/2;
dens=kern_den(variable,h,newx);
Axis2=subplot(1,2,2);
plot(newx,dens,'b-');
xlabel(name);
axis manual;
subplot(Axis1);
axis manual;
Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%

% Main loop
intersav=[];
intersav2=[];
maptest=0;
densitytest=0;
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
    plot(newx,dens,'b-');
    if ~isempty(Iselect)
        if maptest==1
            denspart=kern_den(variable(Iselect),h,newx);
            if max(denspart)>max(dens)
                hold off;
                plot(newx,denspart,'r-');
                hold on;
                plot(newx,dens,'b-');
            else
                plot(newx,denspart,'r-');
            end;
        elseif densitytest==1
            if ~isempty(intersav) & (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
                intersav2=sort([intersav2,intersav]);
            end;
            if ~isempty(intersav2)    
                for i=1:2:length(intersav2)
                    m=intersav2(i);                   
                    M=intersav2(i+1);
                    if i==1
                        ind=find((newx>=m) & (newx<=M));
                        if ~isempty(ind)
                            fill([min(newx(ind)) newx(ind) max(newx(ind))],[0 dens(ind) 0],'m');
                        end;
                    else
                        ind=find((newx>=m) & (newx<=M));
                        if ~isempty(ind)
                            fill([min(newx(ind)) newx(ind) max(newx(ind))],[0 dens(ind) 0],'m');
                            ind=find(newx>=intersav2(i-1)-(newx(2)-newx(1)) & newx<=m+(newx(2)-newx(1)));
                            fill([min(newx(ind)) newx(ind) max(newx(ind))],[0 dens(ind) 0],'w');
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
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'r*');  
            else
                plot(long(Iselect),lat(Iselect),'r.');      
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif densitytest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'ro');  
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
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0      
            maptest=1;
            densitytest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % density selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if densitytest==0
            densitytest=1;
            intersav2=[];
            maptest=0;
            obs=zeros(size(long,1),1);
            if  BUTTON~=3 & BUTTON~=2 
                inter=x;
                intersav=[];
            end;
            p=0;
        end;
        [obs,inter,intersav,p]=selectstat('density',obs,variable,inter,intersav,p,x,BUTTON);
        %%%%%%%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out=obs;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%